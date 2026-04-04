import json
import os

from dataclasses import dataclass

from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from champs.db.models import (
    Base,
    DiscordPlayerMappingRecord,
    MatchPlayerRecord,
    MatchRecord,
    PlayerMappingRecord,
    PlayerRecord,
)
from champs.myresources import PLAYER_TO_NAME, ROLES_BY_CHAMP
from champs.payloads import Match, MatchRow
from champs.random_champs.filters import RoleFilter

K_FACTOR = 32.0
INITIAL_RATING = 1000
VALID_ROLES = {"TOP", "JUNGLE", "MID", "BOT", "SUPP"}
_ROLES_BY_CHAMP_LOWER = {champ.lower(): roles for champ, roles in ROLES_BY_CHAMP.items()}


@dataclass(frozen=True)
class MappingRule:
    name: str
    preferred_role: str | None
    secondary_role: str | None


@dataclass(frozen=True)
class EloRow:
    rank: int
    player: str
    elo: int
    wins: int
    losses: int


@dataclass(frozen=True)
class PlayerMappingOverviewRow:
    name: str
    usernames: tuple[str, ...]
    primary_role: str | None
    secondary_role: str | None
    discord_user_ids: tuple[str, ...]


def _engine(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", future=True)


def init_db(db_path: str) -> None:
    engine = _engine(db_path)
    Base.metadata.create_all(engine)
    _ensure_schema_upgrades(engine)
    with Session(engine) as session:
        _seed_player_mappings(session)
        session.commit()


def _ensure_schema_upgrades(engine) -> None:
    with engine.begin() as conn:
        match_player_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(match_players)")).all()}
        if "player_username" not in match_player_columns:
            conn.execute(text("ALTER TABLE match_players ADD COLUMN player_username VARCHAR"))
            conn.execute(text("UPDATE match_players SET player_username = player_name WHERE player_username IS NULL"))

        mapping_info = conn.execute(text("PRAGMA table_info(player_mappings)")).all()
        if mapping_info:
            mapping_columns = {row[1] for row in mapping_info}
            if "id" not in mapping_columns:
                conn.execute(text("ALTER TABLE player_mappings RENAME TO player_mappings_old"))
                conn.execute(
                    text(
                        """
                        CREATE TABLE player_mappings (
                            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                            username VARCHAR NOT NULL,
                            name VARCHAR NOT NULL,
                            preferred_role VARCHAR,
                            secondary_role VARCHAR,
                            CONSTRAINT uq_player_mapping_rule UNIQUE (username, name, preferred_role, secondary_role)
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO player_mappings (username, name, preferred_role, secondary_role)
                        SELECT username, name, NULL, NULL FROM player_mappings_old
                        """
                    )
                )
                conn.execute(text("DROP TABLE player_mappings_old"))
            else:
                if "preferred_role" not in mapping_columns:
                    conn.execute(text("ALTER TABLE player_mappings ADD COLUMN preferred_role VARCHAR"))
                if "secondary_role" not in mapping_columns:
                    conn.execute(text("ALTER TABLE player_mappings ADD COLUMN secondary_role VARCHAR"))


def _seed_player_mappings(session: Session) -> None:
    for username, name in PLAYER_TO_NAME.items():
        existing = session.scalar(
            select(PlayerMappingRecord).where(
                PlayerMappingRecord.username == username,
                PlayerMappingRecord.name == name,
                PlayerMappingRecord.preferred_role.is_(None),
                PlayerMappingRecord.secondary_role.is_(None),
            )
        )
        if existing is None:
            session.add(
                PlayerMappingRecord(
                    username=username,
                    name=name,
                    preferred_role=None,
                    secondary_role=None,
                )
            )


def set_player_mapping(
    db_path: str,
    username: str,
    name: str,
    preferred_role: str | None = None,
    secondary_role: str | None = None,
) -> None:
    normalized_username = username.strip()
    normalized_name = name.strip()
    normalized_role = RoleFilter.sanitise_filter(preferred_role) if preferred_role else None
    normalized_secondary_role = RoleFilter.sanitise_filter(secondary_role) if secondary_role else None
    if not normalized_username or not normalized_name:
        raise ValueError("Username and name must be non-empty.")

    engine = _engine(db_path)
    with Session(engine) as session:
        default_mapping = session.scalar(
            select(PlayerMappingRecord).where(
                PlayerMappingRecord.username == normalized_username,
                PlayerMappingRecord.name == normalized_name,
                PlayerMappingRecord.preferred_role.is_(None),
                PlayerMappingRecord.secondary_role.is_(None),
            )
        )
        if default_mapping is None:
            session.add(
                PlayerMappingRecord(
                    username=normalized_username,
                    name=normalized_name,
                    preferred_role=None,
                    secondary_role=None,
                )
            )

        if normalized_role:
            # Role preferences are unique per resolved player name.
            # Clear any previous role assignment rows for this name, then store one fresh rule.
            role_rows_for_name = session.scalars(
                select(PlayerMappingRecord).where(
                    PlayerMappingRecord.name == normalized_name,
                    PlayerMappingRecord.preferred_role.is_not(None),
                )
            ).all()
            for row in role_rows_for_name:
                row.preferred_role = None
                row.secondary_role = None

            session.add(
                PlayerMappingRecord(
                    username=normalized_username,
                    name=normalized_name,
                    preferred_role=normalized_role,
                    secondary_role=normalized_secondary_role,
                )
            )
        session.commit()


def set_player_preferred_role(db_path: str, username: str, preferred_role: str) -> None:
    normalized_username = username.strip()
    normalized_role = RoleFilter.sanitise_filter(preferred_role)
    if not normalized_username:
        raise ValueError("Username must be non-empty.")

    engine = _engine(db_path)
    with Session(engine) as session:
        latest = session.scalar(
            select(PlayerMappingRecord)
            .where(PlayerMappingRecord.username == normalized_username)
            .order_by(PlayerMappingRecord.id.desc())
        )
        name = latest.name if latest is not None else normalized_username
        default_mapping = session.scalar(
            select(PlayerMappingRecord).where(
                PlayerMappingRecord.username == normalized_username,
                PlayerMappingRecord.name == name,
                PlayerMappingRecord.preferred_role.is_(None),
                PlayerMappingRecord.secondary_role.is_(None),
            )
        )
        if default_mapping is None:
            session.add(
                PlayerMappingRecord(
                    username=normalized_username,
                    name=name,
                    preferred_role=None,
                    secondary_role=None,
                )
            )

        role_rows_for_name = session.scalars(
            select(PlayerMappingRecord).where(
                PlayerMappingRecord.name == name,
                PlayerMappingRecord.preferred_role.is_not(None),
            )
        ).all()
        for row in role_rows_for_name:
            row.preferred_role = None
            row.secondary_role = None

        session.add(
            PlayerMappingRecord(
                username=normalized_username,
                name=name,
                preferred_role=normalized_role,
                secondary_role=None,
            )
        )
        session.commit()


def set_discord_player_mapping(db_path: str, discord_user_id: int | str, player_username: str) -> None:
    normalized_user_id = str(discord_user_id).strip()
    normalized_username = player_username.strip()
    if not normalized_user_id or not normalized_username:
        raise ValueError("Discord user id and player username must be non-empty.")

    engine = _engine(db_path)
    with Session(engine) as session:
        existing = session.scalar(
            select(DiscordPlayerMappingRecord).where(
                DiscordPlayerMappingRecord.discord_user_id == normalized_user_id
            )
        )
        if existing is None:
            session.add(
                DiscordPlayerMappingRecord(
                    discord_user_id=normalized_user_id,
                    player_username=normalized_username,
                )
            )
        else:
            existing.player_username = normalized_username
        session.commit()


def delete_player_mapping(db_path: str, username: str, name: str) -> int:
    normalized_username = username.strip()
    normalized_name = name.strip()
    if not normalized_username or not normalized_name:
        raise ValueError("Username and name must be non-empty.")

    engine = _engine(db_path)
    with Session(engine) as session:
        rows = session.scalars(
            select(PlayerMappingRecord).where(
                PlayerMappingRecord.username == normalized_username,
                PlayerMappingRecord.name == normalized_name,
            )
        ).all()
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows)


def get_discord_player_mappings(db_path: str, discord_user_ids: list[int] | list[str] | None = None) -> dict[str, str]:
    engine = _engine(db_path)
    with Session(engine) as session:
        query = select(DiscordPlayerMappingRecord)
        if discord_user_ids:
            ids = [str(user_id).strip() for user_id in discord_user_ids if str(user_id).strip()]
            if ids:
                query = query.where(DiscordPlayerMappingRecord.discord_user_id.in_(ids))
        rows = session.scalars(query).all()
    return {row.discord_user_id: row.player_username for row in rows}


def resolve_player_identifier_for_link(db_path: str, identifier: str) -> str | None:
    token = identifier.strip()
    if not token:
        return None

    engine = _engine(db_path)
    with Session(engine) as session:
        mapping_rows = session.scalars(select(PlayerMappingRecord).order_by(PlayerMappingRecord.id.asc())).all()
        player_names = session.scalars(select(PlayerRecord.name)).all()

    # Prefer actual-name matching (case-insensitive).
    canonical_name_by_casefold: dict[str, str] = {}
    for row in mapping_rows:
        canonical_name_by_casefold[row.name.casefold()] = row.name
    for name in player_names:
        canonical_name_by_casefold[name.casefold()] = name
    matched_name = canonical_name_by_casefold.get(token.casefold())
    if matched_name is not None:
        return matched_name

    # Fallback: username mapping (case-sensitive), newest mapping first.
    for row in reversed(mapping_rows):
        if row.username == token:
            return row.name

    return None


def get_player_mapping_overview_rows(
    db_path: str, identifiers: list[str] | None = None
) -> list[PlayerMappingOverviewRow]:
    engine = _engine(db_path)
    with Session(engine) as session:
        mapping_rows = session.scalars(select(PlayerMappingRecord).order_by(PlayerMappingRecord.id.asc())).all()
        discord_rows = session.scalars(select(DiscordPlayerMappingRecord)).all()

    usernames_by_name: dict[str, set[str]] = {}
    latest_role_by_name: dict[str, tuple[str | None, str | None]] = {}
    for row in mapping_rows:
        usernames_by_name.setdefault(row.name, set()).add(row.username)
        if row.preferred_role:
            latest_role_by_name[row.name] = (row.preferred_role, row.secondary_role)

    discord_ids_by_identifier: dict[str, set[str]] = {}
    for row in discord_rows:
        discord_ids_by_identifier.setdefault(row.player_username, set()).add(row.discord_user_id)

    output: list[PlayerMappingOverviewRow] = []
    for name in sorted(usernames_by_name, key=str.casefold):
        usernames = tuple(sorted(usernames_by_name[name], key=str.casefold))
        primary_role, secondary_role = latest_role_by_name.get(name, (None, None))
        discord_ids: set[str] = set()
        discord_ids.update(discord_ids_by_identifier.get(name, set()))
        for username in usernames:
            discord_ids.update(discord_ids_by_identifier.get(username, set()))
        output.append(
            PlayerMappingOverviewRow(
                name=name,
                usernames=usernames,
                primary_role=primary_role,
                secondary_role=secondary_role,
                discord_user_ids=tuple(sorted(discord_ids)),
            )
        )

    if not identifiers:
        return output

    normalized_identifiers = [token.strip() for token in identifiers if token.strip()]
    if not normalized_identifiers:
        return output

    row_by_name_key = {row.name.casefold(): row for row in output}
    names_by_username: dict[str, set[str]] = {}
    for row in output:
        for username in row.usernames:
            names_by_username.setdefault(username, set()).add(row.name)

    selected_names: set[str] = set()
    for token in normalized_identifiers:
        # Prefer actual name resolution over username resolution.
        row = row_by_name_key.get(token.casefold())
        if row is not None:
            selected_names.add(row.name)
            continue

        for name in names_by_username.get(token, set()):
            selected_names.add(name)

    return [row for row in output if row.name in selected_names]


def _resolve_query_names(session: Session, identifiers: list[str]) -> set[str]:
    resolved: list[str] = []
    seen_identifiers: set[str] = set()

    player_names = session.scalars(select(PlayerRecord.name)).all()
    canonical_name_by_casefold = {name.casefold(): name for name in player_names}

    for raw in identifiers:
        token = raw.strip()
        if not token:
            continue
        if token in seen_identifiers:
            continue
        seen_identifiers.add(token)

        mapping_rows = session.scalars(
            select(PlayerMappingRecord)
            .where(PlayerMappingRecord.username == token)
            .order_by(PlayerMappingRecord.id.desc())
        ).all()
        mapped_names: list[str] = []
        for row in mapping_rows:
            if row.name not in mapped_names:
                mapped_names.append(row.name)
            canonical_name_by_casefold.setdefault(row.name.casefold(), row.name)
        if mapped_names:
            if token in mapped_names:
                resolved.append(token)
            else:
                resolved.append(mapped_names[0])
            continue

        canonical_name = canonical_name_by_casefold.get(token.casefold())
        if canonical_name is not None:
            resolved.append(canonical_name)
            continue

        resolved.append(token)

    return set(resolved)


def _mapping_rules(session: Session) -> dict[str, list[MappingRule]]:
    rows = session.scalars(select(PlayerMappingRecord).order_by(PlayerMappingRecord.id.asc())).all()
    by_username: dict[str, list[MappingRule]] = {}
    for row in rows:
        by_username.setdefault(row.username, []).append(
            MappingRule(
                name=row.name,
                preferred_role=row.preferred_role,
                secondary_role=row.secondary_role,
            )
        )
    return by_username


def _champion_roles(champion: str) -> set[str]:
    roles = ROLES_BY_CHAMP.get(champion) or _ROLES_BY_CHAMP_LOWER.get(champion.lower()) or []
    return {role.upper() for role in roles}


def _resolve_rows_to_names(
    mapping_rules: dict[str, list[MappingRule]],
    rows_by_side: dict[str, list[tuple[str, str]]],
) -> dict[tuple[str, int], str]:
    entries: list[tuple[str, int, str, str]] = []
    for side in ("win", "lose"):
        for idx, (username, champion) in enumerate(rows_by_side.get(side, [])):
            entries.append((side, idx, username, champion))

    resolved: dict[tuple[str, int], str] = {}
    for side, idx, username, champion in entries:
        rules = mapping_rules.get(username, [])
        champ_roles = _champion_roles(champion)
        role_rules = [rule for rule in rules if rule.preferred_role]
        matched_role_rules = [rule for rule in role_rules if rule.preferred_role in champ_roles]
        default_rules = [rule for rule in rules if not rule.preferred_role]

        if len(matched_role_rules) == 1:
            resolved[(side, idx)] = matched_role_rules[-1].name
        elif len(matched_role_rules) > 1:
            resolved[(side, idx)] = matched_role_rules[-1].name
        elif default_rules:
            resolved[(side, idx)] = default_rules[-1].name
        else:
            resolved[(side, idx)] = username

    # Preserve previous Wyn/Sean disambiguation when no explicit role rules exist.
    wyn_rules = mapping_rules.get("Wyn", [])
    has_explicit_wyn_role_rule = any(rule.preferred_role for rule in wyn_rules)
    has_explicit_sean_rule = any(rule.name == "Sean" for rule in wyn_rules)
    if not has_explicit_wyn_role_rule and not has_explicit_sean_rule:
        wyn_entries = [(side, idx, champion) for side, idx, username, champion in entries if username == "Wyn"]
        if len(wyn_entries) >= 2:
            bot_flags = [("BOT" in _champion_roles(champion)) for _, _, champion in wyn_entries]
            if sum(bot_flags) == 1:
                for (side, idx, _), is_bot in zip(wyn_entries, bot_flags):
                    resolved[(side, idx)] = "Wyn" if is_bot else "Sean"
            else:
                for i, (side, idx, _) in enumerate(wyn_entries):
                    resolved[(side, idx)] = "Wyn" if i == 0 else "Sean"

    return resolved


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + (10.0 ** ((rating_b - rating_a) / 400.0)))


def _recalculate_ratings(session: Session, reset_players: bool = False) -> None:
    if reset_players:
        session.execute(delete(PlayerRecord))
        ratings: dict[str, float] = {}
    else:
        players = session.scalars(select(PlayerRecord)).all()
        ratings = {player.name: float(INITIAL_RATING) for player in players}

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

    existing_players = {player.name: player for player in session.scalars(select(PlayerRecord)).all()}
    for name, rating in ratings.items():
        if name in existing_players:
            existing_players[name].rating = int(round(rating))
        else:
            session.add(PlayerRecord(name=name, rating=int(round(rating))))


def _refresh_match_player_names_from_mappings(session: Session) -> None:
    mapping_rules = _mapping_rules(session)
    matches = session.scalars(select(MatchRecord).order_by(MatchRecord.timestamp.asc(), MatchRecord.checksum.asc())).all()
    for match in matches:
        match_rows = session.scalars(
            select(MatchPlayerRecord)
            .where(MatchPlayerRecord.match_checksum == match.checksum)
            .order_by(MatchPlayerRecord.id.asc())
        ).all()
        rows_by_side: dict[str, list[tuple[str, str]]] = {"win": [], "lose": []}
        for row in match_rows:
            side = "win" if row.win else "lose"
            username = row.player_username or row.player_name
            rows_by_side[side].append((username, row.champion))
        resolved = _resolve_rows_to_names(mapping_rules, rows_by_side)

        side_index = {"win": 0, "lose": 0}
        for row in match_rows:
            side = "win" if row.win else "lose"
            idx = side_index[side]
            side_index[side] += 1
            username = row.player_username or row.player_name
            row.player_username = username
            row.player_name = resolved[(side, idx)]


def recalculate_all_ratings(db_path: str, refresh_mappings: bool = False) -> None:
    engine = _engine(db_path)
    with Session(engine) as session:
        if refresh_mappings:
            _refresh_match_player_names_from_mappings(session)
        _recalculate_ratings(session, reset_players=refresh_mappings)
        session.commit()


def _ensure_player(session: Session, name: str) -> PlayerRecord:
    player = session.get(PlayerRecord, name)
    if player is None:
        player = PlayerRecord(name=name, rating=INITIAL_RATING)
        session.add(player)
        session.flush()
    return player


def _apply_match_delta(session: Session, winner_names: list[str], loser_names: list[str]) -> None:
    winner_players = [_ensure_player(session, name) for name in winner_names]
    loser_players = [_ensure_player(session, name) for name in loser_names]
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

        mapping_rules = _mapping_rules(session)
        rows_by_side = {
            "win": [(row.player, row.champion) for row in match.win],
            "lose": [(row.player, row.champion) for row in match.lose],
        }
        resolved_names = _resolve_rows_to_names(mapping_rules, rows_by_side)

        winner_names: list[str] = []
        loser_names: list[str] = []
        for side, rows in (("win", match.win), ("lose", match.lose)):
            for idx, row in enumerate(rows):
                resolved_name = resolved_names[(side, idx)]
                _ensure_player(session, resolved_name)
                session.add(
                    MatchPlayerRecord(
                        match_checksum=record.checksum,
                        player_username=row.player,
                        player_name=resolved_name,
                        win=side == "win",
                        champion=row.champion,
                        kda=row.kda,
                    )
                )
                if side == "win":
                    winner_names.append(resolved_name)
                else:
                    loser_names.append(resolved_name)

        _apply_match_delta(session, winner_names=winner_names, loser_names=loser_names)
        session.commit()
        return True


def delete_match(db_path: str, checksum: str) -> bool:
    if not checksum:
        return False
    engine = _engine(db_path)
    with Session(engine) as session:
        record = session.get(MatchRecord, checksum)
        if record is None:
            return False

        session.execute(delete(MatchPlayerRecord).where(MatchPlayerRecord.match_checksum == checksum))
        session.delete(record)
        _recalculate_ratings(session, reset_players=True)
        session.commit()
        return True


def resolve_match_names(db_path: str, match: Match) -> Match:
    engine = _engine(db_path)
    with Session(engine) as session:
        mapping_rules = _mapping_rules(session)
        rows_by_side = {
            "win": [(row.player, row.champion) for row in match.win],
            "lose": [(row.player, row.champion) for row in match.lose],
        }
        resolved_names = _resolve_rows_to_names(mapping_rules, rows_by_side)

    win_rows = [
        MatchRow(
            player=row.player,
            name=resolved_names[("win", idx)],
            champion=row.champion,
            kda=row.kda,
        )
        for idx, row in enumerate(match.win)
    ]
    lose_rows = [
        MatchRow(
            player=row.player,
            name=resolved_names[("lose", idx)],
            champion=row.champion,
            kda=row.kda,
        )
        for idx, row in enumerate(match.lose)
    ]
    return match.model_copy(update={"win": win_rows, "lose": lose_rows})


def get_elo_rows(db_path: str, identifiers: list[str] | None = None) -> list[EloRow]:
    engine = _engine(db_path)
    with Session(engine) as session:
        players = session.scalars(select(PlayerRecord)).all()
        match_rows = session.scalars(select(MatchPlayerRecord)).all()
        filtered_names = _resolve_query_names(session, identifiers or []) if identifiers else None

    records_by_player: dict[str, tuple[int, int]] = {}
    for row in match_rows:
        wins, losses = records_by_player.get(row.player_name, (0, 0))
        if row.win:
            wins += 1
        else:
            losses += 1
        records_by_player[row.player_name] = (wins, losses)

    ordered_players = sorted(players, key=lambda player: (-int(player.rating), player.name.lower()))
    table: list[EloRow] = []
    for idx, player in enumerate(ordered_players, start=1):
        if filtered_names is not None and player.name not in filtered_names:
            continue
        wins, losses = records_by_player.get(player.name, (0, 0))
        table.append(
            EloRow(
                rank=idx,
                player=player.name,
                elo=int(player.rating),
                wins=wins,
                losses=losses,
            )
        )
    return table
