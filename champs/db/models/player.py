from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PlayerRecord(Base):
    __tablename__ = "players"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    custom_points: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    dodges: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    privilege: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    private: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
