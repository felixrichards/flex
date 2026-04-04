from sqlalchemy import func, select
from sqlalchemy.orm import Session

from champs.db import db
from champs.db.models import MatchPlayerRecord, MatchRecord, PlayerRecord
from champs.scoreboard import scoreboard_cv
from champs.payloads import Match
from conftest import resource_path


def test_parse_to_db_pipeline_with_duplicate_guard(tmp_path) -> None:
    db_path = str(tmp_path / "pipeline.db")
    db.init_db(db_path)

    image_path = resource_path("scoreboards", "1.png")
    parsed = scoreboard_cv.detect_post_match(str(image_path))
    match = Match.model_validate(parsed)

    assert db.insert_match(db_path, match) is True
    assert db.insert_match(db_path, match) is False

    engine = db._engine(db_path)
    with Session(engine) as session:
        match_count = session.scalar(select(func.count()).select_from(MatchRecord))
        row_count = session.scalar(select(func.count()).select_from(MatchPlayerRecord))
        player_count = session.scalar(select(func.count()).select_from(PlayerRecord))

    assert match_count == 1
    assert row_count == 10
    assert player_count == 10
