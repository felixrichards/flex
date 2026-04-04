from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DiscordPlayerMappingRecord(Base):
    __tablename__ = "discord_player_mappings"
    __table_args__ = (
        UniqueConstraint("discord_user_id", name="uq_discord_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[str] = mapped_column(String, nullable=False)
    player_username: Mapped[str] = mapped_column(String, nullable=False)
