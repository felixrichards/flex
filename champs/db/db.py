import json
import os

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from champs.constants import DODGE_PENALTY, Privilege
from champs.db.models import (
    Base,
    DiscordPlayerMappingRecord,
    MatchPlayerRecord,
    MatchRecord,
    PlayerDodgePenaltyRecord,
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
    cp: int
    elo: int
    wins: int
    losses: int
    dodges: int
    dodge_scale: float


@dataclass(frozen=True)
class PlayerMappingOverviewRow:
    name: str
    usernames: tuple[str, ...]
    primary_role: str | None
    secondary_role: str | None
    discord_user_ids: tuple[str, ...]


@dataclass(frozen=True)
class PlayerDeleteResult:
    deleted_player_rows: int
    deleted_mapping_rows: int
    deleted_discord_rows: int
    associated_matches: int
    associated_match_rows: int
    deleted_name_variants: tuple[str, ...]


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

        player_info = conn.execute(text("PRAGMA table_info(players)")).all()
        if player_info:
            player_columns = {row[1] for row in player_info}
            if "custom_points" not in player_columns:
                conn.execute(text("ALTER TABLE players ADD COLUMN custom_points INTEGER"))
                conn.execute(
                    text(
                        "UPDATE players SET custom_points = rating "
                        "WHERE custom_points IS NULL"
                    )
                )
            if "dodges" not in player_columns:
                conn.execute(text("ALTER TABLE players ADD COLUMN dodges INTEGER DEFAULT 0"))
                conn.execute(text("UPDATE players SET dodges = 0 WHERE dodges IS NULL"))
            if "privilege" not in player_columns:
                conn.execute(text("ALTER TABLE players ADD COLUMN privilege INTEGER DEFAULT 0"))
                conn.execute(text("UPDATE players SET privilege = 0 WHERE privilege IS NULL"))

        dodge_penalty_info = conn.execute(text("PRAGMA table_info(player_dodge_penalties)")).all()
        if not dodge_penalty_info:
            conn.execute(
                text(
                    """
                    CREATE TABLE player_dodge_penalties (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        player_name VARCHAR NOT NULL,
                        penalty INTEGER NOT NULL,
                        source VARCHAR NOT NULL,
                        channel_id VARCHAR,
                        created_at VARCHAR NOT NULL,
                        FOREIGN KEY(player_name) REFERENCES players (name)
                    )
                    """
                )
            )


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
        canonical_player_name = session.scalar(
            select(PlayerRecord.name)
            .where(func.lower(PlayerRecord.name) == normalized_name.casefold())
            .order_by(PlayerRecord.name.asc())
        )
        canonical_mapping_name = session.scalar(
            select(PlayerMappingRecord.name)
            .where(func.lower(PlayerMappingRecord.name) == normalized_name.casefold())
            .order_by(PlayerMappingRecord.id.desc())
        )
        canonical_name = canonical_player_name or canonical_mapping_name or normalized_name

        default_mapping = session.scalar(
            select(PlayerMappingRecord).where(
                PlayerMappingRecord.username == normalized_username,
                PlayerMappingRecord.name == canonical_name,
                PlayerMappingRecord.preferred_role.is_(None),
                PlayerMappingRecord.secondary_role.is_(None),
            )
        )
        if default_mapping is None:
            session.add(
                PlayerMappingRecord(
                    username=normalized_username,
                    name=canonical_name,
                    preferred_role=None,
                    secondary_role=None,
                )
            )

        if normalized_role:
            # Role preferences are unique per resolved player name.
            # Clear any previous role assignment rows for this name, then store one fresh rule.
            role_rows_for_name = session.scalars(
                select(PlayerMappingRecord).where(
                    func.lower(PlayerMappingRecord.name) == canonical_name.casefold(),
                    PlayerMappingRecord.preferred_role.is_not(None),
                )
            ).all()
            for row in role_rows_for_name:
                row.preferred_role = None
                row.secondary_role = None

            session.add(
                PlayerMappingRecord(
                    username=normalized_username,
                    name=canonical_name,
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


def delete_player_completely(db_path: str, name: str) -> PlayerDeleteResult:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Name must be non-empty.")

    target_casefold = normalized_name.casefold()
    engine = _engine(db_path)
    with Session(engine) as session:
        mapping_rows = session.scalars(select(PlayerMappingRecord)).all()
        player_rows = session.scalars(select(PlayerRecord)).all()
        match_rows = session.scalars(select(MatchPlayerRecord)).all()
        discord_rows = session.scalars(select(DiscordPlayerMappingRecord)).all()

        # Exact-case deletion first, so legacy bad-case duplicates can be cleaned up
        # without being blocked by another case variant that has match history.
        exact_name_exists = any(row.name == normalized_name for row in mapping_rows) or any(
            row.name == normalized_name for row in player_rows
        )
        if exact_name_exists:
            target_mapping_rows = [row for row in mapping_rows if row.name == normalized_name]
            target_name_variants = {normalized_name}
            target_match_rows = [row for row in match_rows if row.player_name == normalized_name]
            target_match_checksums = {row.match_checksum for row in target_match_rows}
            if target_match_rows:
                return PlayerDeleteResult(
                    deleted_player_rows=0,
                    deleted_mapping_rows=0,
                    deleted_discord_rows=0,
                    associated_matches=len(target_match_checksums),
                    associated_match_rows=len(target_match_rows),
                    deleted_name_variants=tuple(sorted(target_name_variants, key=str.casefold)),
                )

            deleted_mapping_rows = 0
            for row in target_mapping_rows:
                session.delete(row)
                deleted_mapping_rows += 1

            deleted_player_rows = 0
            for row in player_rows:
                if row.name == normalized_name:
                    session.delete(row)
                    deleted_player_rows += 1

            target_usernames = {row.username for row in target_mapping_rows}
            surviving_usernames = {row.username for row in mapping_rows if row.name != normalized_name}
            removable_usernames = target_usernames - surviving_usernames

            deleted_discord_rows = 0
            for row in discord_rows:
                if row.player_username == normalized_name or row.player_username in removable_usernames:
                    session.delete(row)
                    deleted_discord_rows += 1

            session.commit()
            return PlayerDeleteResult(
                deleted_player_rows=deleted_player_rows,
                deleted_mapping_rows=deleted_mapping_rows,
                deleted_discord_rows=deleted_discord_rows,
                associated_matches=0,
                associated_match_rows=0,
                deleted_name_variants=tuple(sorted(target_name_variants, key=str.casefold)),
            )

        target_mapping_rows = [row for row in mapping_rows if row.name.casefold() == target_casefold]
        target_usernames_casefold = {row.username.casefold() for row in target_mapping_rows}

        target_name_variants = {row.name for row in target_mapping_rows}
        target_name_variants.update(row.name for row in player_rows if row.name.casefold() == target_casefold)
        target_name_variants.update(row.player_name for row in match_rows if row.player_name.casefold() == target_casefold)
        target_name_variants_casefold = {value.casefold() for value in target_name_variants}
        if not target_name_variants_casefold:
            target_name_variants_casefold.add(target_casefold)

        target_match_rows = [row for row in match_rows if row.player_name.casefold() in target_name_variants_casefold]
        target_match_checksums = {row.match_checksum for row in target_match_rows}
        if target_match_rows:
            return PlayerDeleteResult(
                deleted_player_rows=0,
                deleted_mapping_rows=0,
                deleted_discord_rows=0,
                associated_matches=len(target_match_checksums),
                associated_match_rows=len(target_match_rows),
                deleted_name_variants=tuple(sorted(target_name_variants, key=str.casefold)),
            )

        deleted_mapping_rows = 0
        for row in target_mapping_rows:
            session.delete(row)
            deleted_mapping_rows += 1

        deleted_discord_rows = 0
        for row in discord_rows:
            identifier = row.player_username.casefold()
            if identifier in target_name_variants_casefold or identifier in target_usernames_casefold:
                session.delete(row)
                deleted_discord_rows += 1

        deleted_player_rows = sum(1 for row in player_rows if row.name.casefold() in target_name_variants_casefold)
        for row in player_rows:
            if row.name.casefold() in target_name_variants_casefold:
                session.delete(row)

        session.commit()
        return PlayerDeleteResult(
            deleted_player_rows=deleted_player_rows,
            deleted_mapping_rows=deleted_mapping_rows,
            deleted_discord_rows=deleted_discord_rows,
            associated_matches=0,
            associated_match_rows=0,
            deleted_name_variants=tuple(sorted(target_name_variants, key=str.casefold)),
        )


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
    engine = _engine(db_path)
    with Session(engine) as session:
        return resolve_player_identifier_for_link_with_session(session, identifier)


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

    output_with_discord: list[PlayerMappingOverviewRow] = []
    for name in sorted(usernames_by_name, key=str.casefold):
        usernames = tuple(sorted(usernames_by_name[name], key=str.casefold))
        primary_role, secondary_role = latest_role_by_name.get(name, (None, None))
        output_with_discord.append(
            PlayerMappingOverviewRow(
                name=name,
                usernames=usernames,
                primary_role=primary_role,
                secondary_role=secondary_role,
                discord_user_ids=tuple(),
            )
        )

    row_by_name_key = {row.name.casefold(): row for row in output_with_discord}
    names_by_username: dict[str, set[str]] = {}
    for row in output_with_discord:
        for username in row.usernames:
            names_by_username.setdefault(username, set()).add(row.name)

    # Resolve each discord link to exactly one actual player name when possible.
    # Priority:
    # 1) exact/ci actual-name match
    # 2) legacy username link only if username uniquely maps to one name
    discord_ids_by_name: dict[str, set[str]] = {}
    for row in discord_rows:
        identifier = row.player_username
        matched_row = row_by_name_key.get(identifier.casefold())
        if matched_row is not None:
            discord_ids_by_name.setdefault(matched_row.name, set()).add(row.discord_user_id)
            continue
        name_candidates = names_by_username.get(identifier, set())
        if len(name_candidates) == 1:
            name = next(iter(name_candidates))
            discord_ids_by_name.setdefault(name, set()).add(row.discord_user_id)

    output_with_discord = [
        PlayerMappingOverviewRow(
            name=row.name,
            usernames=row.usernames,
            primary_role=row.primary_role,
            secondary_role=row.secondary_role,
            discord_user_ids=tuple(sorted(discord_ids_by_name.get(row.name, set()))),
        )
        for row in output_with_discord
    ]

    if not identifiers:
        return output_with_discord

    normalized_identifiers = [token.strip() for token in identifiers if token.strip()]
    if not normalized_identifiers:
        return output_with_discord

    selected_names: set[str] = set()
    for token in normalized_identifiers:
        # Prefer actual name resolution over username resolution.
        row = row_by_name_key.get(token.casefold())
        if row is not None:
            selected_names.add(row.name)
            continue

        for name in names_by_username.get(token, set()):
            selected_names.add(name)

    return [row for row in output_with_discord if row.name in selected_names]


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
    players = session.scalars(select(PlayerRecord)).all()
    preserved_metadata = {
        player.name: (int(player.custom_points), int(player.dodges), int(player.privilege))
        for player in players
    }
    if reset_players:
        session.execute(delete(PlayerRecord))
        ratings: dict[str, float] = {}
        players = []
    else:
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

    penalty_rows = session.scalars(select(PlayerDodgePenaltyRecord)).all()
    penalty_sum_by_player: dict[str, int] = {}
    dodge_count_by_player: dict[str, int] = {}
    for row in penalty_rows:
        penalty_sum_by_player[row.player_name] = penalty_sum_by_player.get(row.player_name, 0) + int(row.penalty)
        dodge_count_by_player[row.player_name] = dodge_count_by_player.get(row.player_name, 0) + 1

    existing_players = {player.name: player for player in session.scalars(select(PlayerRecord)).all()}
    for name, rating in ratings.items():
        rounded = int(round(rating))
        applied_penalties = penalty_sum_by_player.get(name, 0)
        dodge_count = dodge_count_by_player.get(name, 0)
        if name in existing_players:
            existing_players[name].rating = rounded
            existing_players[name].custom_points = rounded - applied_penalties
            existing_players[name].dodges = dodge_count
        else:
            _cp, _dodges, privilege = preserved_metadata.get(
                name,
                (rounded, 0, int(Privilege.PLAYER)),
            )
            session.add(
                PlayerRecord(
                    name=name,
                    rating=rounded,
                    custom_points=rounded - applied_penalties,
                    dodges=dodge_count,
                    privilege=privilege,
                )
            )


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
        player = PlayerRecord(
            name=name,
            rating=INITIAL_RATING,
            custom_points=INITIAL_RATING,
            dodges=0,
            privilege=int(Privilege.PLAYER),
        )
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
        next_rating = int(round(float(player.rating) + delta))
        player.custom_points = int(player.custom_points) + (next_rating - int(player.rating))
        player.rating = next_rating
    for player in loser_players:
        next_rating = int(round(float(player.rating) - delta))
        player.custom_points = int(player.custom_points) + (next_rating - int(player.rating))
        player.rating = next_rating


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


def _count_games_by_player(match_rows: list[MatchPlayerRecord]) -> dict[str, int]:
    games_by_player: dict[str, int] = {}
    for row in match_rows:
        games_by_player[row.player_name] = games_by_player.get(row.player_name, 0) + 1
    return games_by_player


def dodge_scale_for_player(dodges: int, games_played: int) -> float:
    safe_games = max(1, int(games_played))
    safe_dodges = max(0, int(dodges))
    return 1.0 + (float(safe_dodges) / float(safe_games))


def apply_dodge_penalty(
    db_path: str,
    player_name: str,
    base_penalty: float,
    *,
    source: str = "dodge",
    channel_id: int | str | None = None,
) -> int:
    normalized_player = player_name.strip()
    if not normalized_player:
        raise ValueError("Player name must be non-empty.")
    if base_penalty < 0:
        raise ValueError("Base penalty must be non-negative.")

    engine = _engine(db_path)
    with Session(engine) as session:
        player = session.scalar(
            select(PlayerRecord).where(func.lower(PlayerRecord.name) == normalized_player.casefold())
        )
        if player is None:
            raise ValueError(f"Unknown player: {player_name}")

        match_rows = session.scalars(select(MatchPlayerRecord)).all()
        games_by_player = _count_games_by_player(match_rows)
        games_played = games_by_player.get(player.name, 0)
        scale = dodge_scale_for_player(int(player.dodges), games_played)
        penalty = int(round(float(base_penalty) * scale))

        player.custom_points = int(player.custom_points) - penalty
        player.dodges = int(player.dodges) + 1
        session.add(
            PlayerDodgePenaltyRecord(
                player_name=player.name,
                penalty=penalty,
                source=source,
                channel_id=str(channel_id) if channel_id is not None else None,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        session.commit()
        return penalty


def undo_recent_dodge_penalties(db_path: str, player_name: str, count: int = 1) -> int:
    normalized_player = player_name.strip()
    if not normalized_player:
        raise ValueError("Player name must be non-empty.")
    if count <= 0:
        return 0

    engine = _engine(db_path)
    with Session(engine) as session:
        player = session.scalar(
            select(PlayerRecord).where(func.lower(PlayerRecord.name) == normalized_player.casefold())
        )
        if player is None:
            raise ValueError(f"Unknown player: {player_name}")

        penalties = session.scalars(
            select(PlayerDodgePenaltyRecord)
            .where(PlayerDodgePenaltyRecord.player_name == player.name)
            .order_by(PlayerDodgePenaltyRecord.id.desc())
        ).all()
        if len(penalties) < count:
            raise ValueError(f"Cannot undo {count} dodge(s): player has only {len(penalties)} applied dodge(s).")

        restored = 0
        for row in penalties[:count]:
            restored += int(row.penalty)
            session.delete(row)
            player.dodges = max(0, int(player.dodges) - 1)

        player.custom_points = int(player.custom_points) + restored
        session.commit()
        return restored


def resolve_player_identifier(db_path: str, identifier: str) -> str | None:
    token = identifier.strip()
    if not token:
        return None

    engine = _engine(db_path)
    with Session(engine) as session:
        return resolve_player_identifier_for_link_with_session(session, token)


def resolve_player_identifier_for_link_with_session(session: Session, identifier: str) -> str | None:
    token = identifier.strip()
    if not token:
        return None

    mapping_rows = session.scalars(select(PlayerMappingRecord).order_by(PlayerMappingRecord.id.asc())).all()
    player_names = session.scalars(select(PlayerRecord.name)).all()

    canonical_name_by_casefold: dict[str, str] = {}
    for row in mapping_rows:
        canonical_name_by_casefold[row.name.casefold()] = row.name
    for name in player_names:
        canonical_name_by_casefold[name.casefold()] = name
    matched_name = canonical_name_by_casefold.get(token.casefold())
    if matched_name is not None:
        return matched_name

    for row in reversed(mapping_rows):
        if row.username == token:
            return row.name
    return None


def get_player_privilege(db_path: str, identifier: str) -> int:
    resolved_name = resolve_player_identifier(db_path, identifier)
    if resolved_name is None:
        return int(Privilege.PLAYER)
    engine = _engine(db_path)
    with Session(engine) as session:
        player = session.get(PlayerRecord, resolved_name)
        if player is None:
            return int(Privilege.PLAYER)
        return int(player.privilege or 0)


def set_player_privilege(db_path: str, identifier: str, privilege: int) -> str:
    normalized_privilege = int(privilege)
    if normalized_privilege not in {int(level) for level in Privilege}:
        raise ValueError("Privilege must be one of: 0, 1, 2, 3.")

    engine = _engine(db_path)
    with Session(engine) as session:
        resolved_name = resolve_player_identifier_for_link_with_session(session, identifier)
        if resolved_name is None:
            raise ValueError(f"Unknown player: {identifier}")
        player = session.get(PlayerRecord, resolved_name)
        if player is None:
            player = PlayerRecord(
                name=resolved_name,
                rating=INITIAL_RATING,
                custom_points=INITIAL_RATING,
                dodges=0,
                privilege=normalized_privilege,
            )
            session.add(player)
        else:
            player.privilege = normalized_privilege
        session.commit()
        return resolved_name


def get_discord_linked_player_name(db_path: str, discord_user_id: int | str) -> str | None:
    normalized_user_id = str(discord_user_id).strip()
    if not normalized_user_id:
        return None
    engine = _engine(db_path)
    with Session(engine) as session:
        row = session.scalar(
            select(DiscordPlayerMappingRecord).where(DiscordPlayerMappingRecord.discord_user_id == normalized_user_id)
        )
        if row is None:
            return None
        return resolve_player_identifier_for_link_with_session(session, row.player_username)


def get_discord_user_privilege(db_path: str, discord_user_id: int | str) -> int:
    linked_name = get_discord_linked_player_name(db_path, discord_user_id)
    if linked_name is None:
        return int(Privilege.PLAYER)
    return get_player_privilege(db_path, linked_name)


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

    ordered_players = sorted(
        players,
        key=lambda player: (-int(player.custom_points), -int(player.rating), player.name.lower()),
    )
    table: list[EloRow] = []
    games_by_player = _count_games_by_player(match_rows)
    for idx, player in enumerate(ordered_players, start=1):
        if filtered_names is not None and player.name not in filtered_names:
            continue
        wins, losses = records_by_player.get(player.name, (0, 0))
        games = games_by_player.get(player.name, 0)
        dodge_scale = dodge_scale_for_player(int(player.dodges), games)
        table.append(
            EloRow(
                rank=idx,
                player=player.name,
                cp=int(player.custom_points),
                elo=int(player.rating),
                wins=wins,
                losses=losses,
                dodges=int(player.dodges),
                dodge_scale=dodge_scale,
            )
        )
    return table
