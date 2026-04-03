import json
import os

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import select

from champs.models import Base, MatchPlayerRecord, MatchRecord, PlayerRecord
from champs.payloads import Match

K_FACTOR = 32.0
INITIAL_RATING = 1000


def _engine(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", future=True)


def init_db(db_path: str) -> None:
    engine = _engine(db_path)
    Base.metadata.create_all(engine)


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + (10.0 ** ((rating_b - rating_a) / 400.0)))


def _recalculate_ratings(session: Session) -> None:
    players = session.scalars(select(PlayerRecord)).all()
    ratings: dict[str, float] = {player.name: float(INITIAL_RATING) for player in players}

    matches = session.scalars(
        select(MatchRecord).order_by(MatchRecord.timestamp.asc(), MatchRecord.checksum.asc())
    ).all()

    for match in matches:
        rows = session.scalars(
            select(MatchPlayerRecord).where(MatchPlayerRecord.match_checksum == match.checksum)
        ).all()
        winners = [row.player_name for row in rows if row.win]
        losers = [row.player_name for row in rows if not row.win]
        if not winners or not losers:
            continue

        winner_avg = sum(ratings.get(name, float(INITIAL_RATING)) for name in winners) / len(winners)
        loser_avg = sum(ratings.get(name, float(INITIAL_RATING)) for name in losers) / len(losers)

        expected_win = _expected_score(winner_avg, loser_avg)
        delta = K_FACTOR * (1.0 - expected_win)

        for name in winners:
            ratings[name] = ratings.get(name, float(INITIAL_RATING)) + delta
        for name in losers:
            ratings[name] = ratings.get(name, float(INITIAL_RATING)) - delta

    for player in players:
        player.rating = int(round(ratings.get(player.name, float(INITIAL_RATING))))


def recalculate_all_ratings(db_path: str) -> None:
    engine = _engine(db_path)
    with Session(engine) as session:
        _recalculate_ratings(session)
        session.commit()


def _ensure_player(session: Session, name: str) -> PlayerRecord:
    player = session.get(PlayerRecord, name)
    if player is None:
        player = PlayerRecord(name=name, rating=INITIAL_RATING)
        session.add(player)
        session.flush()
    return player


def _apply_match_delta(session: Session, match: Match) -> None:
    winner_players = [_ensure_player(session, row.player) for row in match.win]
    loser_players = [_ensure_player(session, row.player) for row in match.lose]
    if not winner_players or not loser_players:
        return

    winner_avg = sum(float(player.rating) for player in winner_players) / len(winner_players)
    loser_avg = sum(float(player.rating) for player in loser_players) / len(loser_players)
    expected_win = _expected_score(winner_avg, loser_avg)
    delta = K_FACTOR * (1.0 - expected_win)

    for player in winner_players:
        player.rating = int(round(float(player.rating) + delta))
    for player in loser_players:
        player.rating = int(round(float(player.rating) - delta))


def insert_match(db_path: str, match: Match) -> bool:
    if not match.checksum:
        return False
    payload = json.dumps(match.model_dump(mode="json"), separators=(",", ":"))
    engine = _engine(db_path)
    with Session(engine) as session:
        if session.get(MatchRecord, match.checksum) is not None:
            return False
        record = MatchRecord(
            checksum=match.checksum or "",
            timestamp=match.timestamp.isoformat(),
            payload=payload,
        )
        session.add(record)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            return False

        for side, rows in (("win", match.win), ("lose", match.lose)):
            for row in rows:
                _ensure_player(session, row.player)
                session.add(
                    MatchPlayerRecord(
                        match_checksum=record.checksum,
                        player_name=row.player,
                        win=side == "win",
                        champion=row.champion,
                        kda=row.kda,
                    )
                )

        _apply_match_delta(session, match)
        session.commit()
        return True
