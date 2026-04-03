from sqlalchemy import select
from sqlalchemy.orm import Session

from champs import db
from champs.models import MatchRecord, PlayerRecord
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
