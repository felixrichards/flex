from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MatchRecord(Base):
    __tablename__ = "matches"

    checksum: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class MatchPlayerRecord(Base):
    __tablename__ = "match_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_checksum: Mapped[str] = mapped_column(String, ForeignKey("matches.checksum"), nullable=False)
    player_username: Mapped[str] = mapped_column(String, nullable=False)
    player_name: Mapped[str] = mapped_column(String, ForeignKey("players.name"), nullable=False)
    win: Mapped[bool] = mapped_column(nullable=False)
    champion: Mapped[str] = mapped_column(String, nullable=False)
    kda: Mapped[str] = mapped_column(String, nullable=False)
