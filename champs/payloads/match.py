from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator


class MatchRow(BaseModel):
    player: str = Field(..., min_length=1)
    name: str | None = None
    champion: str = Field(..., min_length=1)
    kda: str = Field(..., min_length=1)


class Match(BaseModel):
    win: list[MatchRow]
    lose: list[MatchRow]
    date: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    checksum: str | None = None

    @field_validator("win", "lose")
    @classmethod
    def _validate_team_size(cls, value: list[MatchRow]) -> list[MatchRow]:
        if len(value) != 5:
            raise ValueError("Each team must have exactly 5 rows.")
        return value

    @staticmethod
    def _checksum_payload(rows: list[MatchRow]) -> list[dict]:
        payload = [
            {"player": row.player, "champion": row.champion, "kda": row.kda}
            for row in rows
        ]
        payload.sort(key=lambda item: (item["player"], item["champion"], item["kda"]))
        return payload

    @classmethod
    def _calculate_checksum(cls, win: list[MatchRow], lose: list[MatchRow]) -> str:
        payload = {
            "win": cls._checksum_payload(win),
            "lose": cls._checksum_payload(lose),
        }
        packed = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(packed.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def _set_checksum(self) -> "Match":
        computed = self._calculate_checksum(self.win, self.lose)
        if self.checksum is None or self.checksum != computed:
            self.checksum = computed
        return self
