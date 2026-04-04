from pydantic import BaseModel, Field


class PlayerMappingRow(BaseModel):
    username: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    primary_role: str | None = None
    secondary_role: str | None = None


class PlayerMappingImport(BaseModel):
    players: list[PlayerMappingRow]
