from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


class FearlessMatch(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    champs: list[str]

    @field_validator("champs")
    @classmethod
    def _validate_champs(cls, value: list[str]) -> list[str]:
        cleaned = [champ.strip() for champ in value if champ and champ.strip()]
        if len(cleaned) != 10:
            raise ValueError("Fearless matches must contain exactly 10 champions.")
        if len(set(cleaned)) != 10:
            raise ValueError("Fearless matches must contain 10 unique champions.")
        return cleaned


class FearlessState(BaseModel):
    enabled: bool = False
    start: datetime | None = None
    banned: list[str] = Field(default_factory=list)
    matches: list[FearlessMatch] = Field(default_factory=list)
