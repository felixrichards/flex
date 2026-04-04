from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PlayerMappingRecord(Base):
    __tablename__ = "player_mappings"
    __table_args__ = (
        UniqueConstraint(
            "username",
            "name",
            "preferred_role",
            "secondary_role",
            name="uq_player_mapping_rule",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    preferred_role: Mapped[str | None] = mapped_column(String, nullable=True)
    secondary_role: Mapped[str | None] = mapped_column(String, nullable=True)
