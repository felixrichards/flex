import itertools
import random
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from champs.db import db
from champs.db.models import PlayerMappingRecord, PlayerRecord

ROLES: tuple[str, ...] = ("TOP", "JUNGLE", "MID", "BOT", "SUPP")
SECONDARY_ROLE_PENALTY = 20
OFF_ROLE_PENALTY = 40
RANDOM_GAP_SLACK = 10
RANDOM_PENALTY_SLACK = 20

DRAFT_HELP = """`champsdraft` usage:

- `champsdraft`
  Use players currently in voice channels.

- `champsdraft <player_or_username> ...`
  Use an explicit player list (must resolve to 10 players).

- `champsdraft [<player_or_username> ...] [+player ...] [-player ...]`
  `+` opts a player in and `-` opts a player out.
  If no explicit list is provided, voice-channel players are used as the base.
"""


@dataclass(frozen=True)
class DraftPlayer:
    name: str
    elo: int
    primary_role: str | None
    secondary_role: str | None


@dataclass(frozen=True)
class TeamAssignment:
    role: str
    player: DraftPlayer
    penalty: int
    adjusted_elo: int


@dataclass(frozen=True)
class TeamDraft:
    assignments: tuple[TeamAssignment, ...]
    raw_total_elo: int
    adjusted_total_elo: int
    total_penalty: int


@dataclass(frozen=True)
class DraftResult:
    blue: TeamDraft
    red: TeamDraft


@dataclass(frozen=True)
class MappingRule:
    username: str
    name: str
    primary_role: str | None
    secondary_role: str | None


@dataclass(frozen=True)
class _ResolverState:
    latest_name_by_username: dict[str, str]
    latest_mapping_by_username: dict[str, MappingRule]
    latest_mapping_by_name_casefold: dict[str, MappingRule]
    player_username_by_discord_id: dict[str, str]
    canonical_name_by_casefold: dict[str, str]
    role_pref_by_name_casefold: dict[str, tuple[str | None, str | None]]
    rating_by_name_casefold: dict[str, int]


def _clean_token(token: str) -> str:
    return token.strip().strip(",")


def _build_resolver_state(db_path: str) -> _ResolverState:
    engine = db._engine(db_path)
    with Session(engine) as session:
        mappings = session.scalars(select(PlayerMappingRecord).order_by(PlayerMappingRecord.id.asc())).all()
        players = session.scalars(select(PlayerRecord)).all()
    discord_player_mappings = db.get_discord_player_mappings(db_path)

    latest_name_by_username: dict[str, str] = {}
    latest_mapping_by_username: dict[str, MappingRule] = {}
    latest_mapping_by_name_casefold: dict[str, MappingRule] = {}
    canonical_name_by_casefold: dict[str, str] = {}
    role_pref_by_name_casefold: dict[str, tuple[str | None, str | None]] = {}
    rating_by_name_casefold = {row.name.casefold(): int(row.rating) for row in players}

    for row in mappings:
        mapping_rule = MappingRule(
            username=row.username,
            name=row.name,
            primary_role=row.preferred_role,
            secondary_role=row.secondary_role,
        )
        latest_name_by_username[row.username.casefold()] = row.name
        latest_mapping_by_username[row.username.casefold()] = mapping_rule
        latest_mapping_by_name_casefold[row.name.casefold()] = mapping_rule
        canonical_name_by_casefold[row.name.casefold()] = row.name
        if row.preferred_role:
            role_pref_by_name_casefold[row.name.casefold()] = (row.preferred_role, row.secondary_role)

    for row in players:
        canonical_name_by_casefold[row.name.casefold()] = row.name

    return _ResolverState(
        latest_name_by_username=latest_name_by_username,
        latest_mapping_by_username=latest_mapping_by_username,
        latest_mapping_by_name_casefold=latest_mapping_by_name_casefold,
        player_username_by_discord_id=discord_player_mappings,
        canonical_name_by_casefold=canonical_name_by_casefold,
        role_pref_by_name_casefold=role_pref_by_name_casefold,
        rating_by_name_casefold=rating_by_name_casefold,
    )


def _resolve_mapping_rule(identifier: str, state: _ResolverState) -> MappingRule | None:
    token = _clean_token(identifier)
    if not token:
        return None
    token_key = token.casefold()
    canonical_name = state.canonical_name_by_casefold.get(token_key)
    if canonical_name is not None:
        by_name = state.latest_mapping_by_name_casefold.get(canonical_name.casefold())
        if by_name is not None:
            return by_name
    return state.latest_mapping_by_username.get(token_key)


def _resolve_player_identifier(identifier: str, state: _ResolverState) -> DraftPlayer | None:
    token = _clean_token(identifier)
    if not token:
        return None

    token_key = token.casefold()
    canonical_name = state.canonical_name_by_casefold.get(token_key)
    if canonical_name is None:
        canonical_name = state.latest_name_by_username.get(token_key, token)

    name_key = canonical_name.casefold()
    elo = state.rating_by_name_casefold.get(name_key, db.INITIAL_RATING)
    primary_role, secondary_role = state.role_pref_by_name_casefold.get(name_key, (None, None))
    return DraftPlayer(
        name=canonical_name,
        elo=int(elo),
        primary_role=primary_role,
        secondary_role=secondary_role,
    )


def _resolve_players(identifiers: list[str], state: _ResolverState) -> list[DraftPlayer]:
    resolved: list[DraftPlayer] = []
    seen: set[str] = set()
    for token in identifiers:
        player = _resolve_player_identifier(token, state)
        if player is None:
            continue
        key = player.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(player)
    return resolved


def _extract_voice_tokens(ctx, player_username_by_discord_id: dict[str, str]) -> list[str]:
    guild = ctx.guild
    if guild is None:
        return []

    afk_channel_id = guild.afk_channel.id if guild.afk_channel else None
    tokens: list[str] = []
    for channel in guild.voice_channels:
        if afk_channel_id is not None and channel.id == afk_channel_id:
            continue
        for member in channel.members:
            if member.bot:
                continue
            mapped_player_username = player_username_by_discord_id.get(str(member.id))
            # Voice auto-detection is Discord-ID driven only.
            # If a voice user is not linked, they are ignored.
            if not mapped_player_username:
                continue
            if mapped_player_username not in tokens:
                tokens.append(mapped_player_username)
    return tokens


def _parse_draft_args(args) -> tuple[list[str], list[str], list[str], bool]:
    explicit: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    wants_help = False
    for raw in args:
        token = _clean_token(raw)
        if not token:
            continue
        if token.lower() in {"help", "--help", "-h"}:
            wants_help = True
            continue
        if token.startswith("+") and len(token) > 1:
            added.append(token[1:])
            continue
        if token.startswith("-") and len(token) > 1:
            removed.append(token[1:])
            continue
        explicit.append(token)
    return explicit, added, removed, wants_help


def _role_penalty(player: DraftPlayer, role: str) -> int:
    primary = player.primary_role
    secondary = player.secondary_role
    if not primary:
        return 0
    if role == primary:
        return 0
    if secondary and role == secondary:
        return SECONDARY_ROLE_PENALTY
    return OFF_ROLE_PENALTY


def _best_team_assignment(players: tuple[DraftPlayer, ...]) -> TeamDraft:
    best: TeamDraft | None = None
    best_key = None
    for roles in itertools.permutations(ROLES, len(players)):
        assignments: list[TeamAssignment] = []
        raw_total = 0
        adjusted_total = 0
        total_penalty = 0
        for player, role in zip(players, roles):
            penalty = _role_penalty(player, role)
            adjusted = player.elo - penalty
            raw_total += player.elo
            adjusted_total += adjusted
            total_penalty += penalty
            assignments.append(
                TeamAssignment(
                    role=role,
                    player=player,
                    penalty=penalty,
                    adjusted_elo=adjusted,
                )
            )
        ordered_assignments = tuple(sorted(assignments, key=lambda row: ROLES.index(row.role)))
        key = (
            total_penalty,
            -adjusted_total,
            tuple(row.player.name.casefold() for row in ordered_assignments),
        )
        if best is None or key < best_key:
            best = TeamDraft(
                assignments=ordered_assignments,
                raw_total_elo=raw_total,
                adjusted_total_elo=adjusted_total,
                total_penalty=total_penalty,
            )
            best_key = key
    if best is None:
        raise ValueError("Could not assign team roles.")
    return best


def _build_draft(
    players: list[DraftPlayer],
    *,
    randomize: bool = False,
    rng: random.Random | None = None,
) -> DraftResult:
    if len(players) != len(ROLES) * 2:
        raise ValueError("Exactly 10 unique players are required.")

    indexed_players = list(players)
    team_size = len(ROLES)
    assignment_cache: dict[tuple[int, ...], TeamDraft] = {}

    def assign(indices: tuple[int, ...]) -> TeamDraft:
        cached = assignment_cache.get(indices)
        if cached is not None:
            return cached
        team_players = tuple(indexed_players[i] for i in indices)
        drafted = _best_team_assignment(team_players)
        assignment_cache[indices] = drafted
        return drafted

    candidate_results: list[tuple[tuple[int, int, tuple[str, ...], tuple[str, ...]], DraftResult]] = []
    all_indices = tuple(range(len(indexed_players)))
    for blue_indices in itertools.combinations(all_indices, team_size):
        if 0 not in blue_indices:
            continue
        red_indices = tuple(i for i in all_indices if i not in blue_indices)
        blue = assign(blue_indices)
        red = assign(red_indices)
        adjusted_gap = abs(blue.adjusted_total_elo - red.adjusted_total_elo)
        key = (
            adjusted_gap,
            blue.total_penalty + red.total_penalty,
            tuple(row.player.name.casefold() for row in blue.assignments),
            tuple(row.player.name.casefold() for row in red.assignments),
        )
        candidate_results.append((key, DraftResult(blue=blue, red=red)))

    if not candidate_results:
        raise ValueError("Could not build balanced teams.")

    candidate_results.sort(key=lambda item: item[0])
    if not randomize:
        return candidate_results[0][1]

    rand = rng or random.Random()
    best_gap = candidate_results[0][0][0]
    best_penalty = min(key[1] for key, _ in candidate_results if key[0] == best_gap)

    pool = [
        result
        for key, result in candidate_results
        if key[0] <= best_gap + RANDOM_GAP_SLACK and key[1] <= best_penalty + RANDOM_PENALTY_SLACK
    ]
    if not pool:
        pool = [candidate_results[0][1]]
    return rand.choice(pool)


def _fit_label(penalty: int) -> str:
    if penalty == 0:
        return "Primary"
    if penalty == SECONDARY_ROLE_PENALTY:
        return "Secondary"
    return "Off-role"


def _format_team_table(name: str, team: TeamDraft) -> str:
    role_width = max(len("Role"), *(len(row.role) for row in team.assignments))
    player_width = max(len("Player"), *(len(row.player.name) for row in team.assignments))
    elo_width = max(len("ELO"), *(len(str(row.player.elo)) for row in team.assignments))
    adjusted_width = max(len("Adj"), *(len(str(row.adjusted_elo)) for row in team.assignments))
    fit_width = max(len("Fit"), *(len(_fit_label(row.penalty)) for row in team.assignments))

    lines = [
        name,
        (
            f"{'Role'.ljust(role_width)}  {'Player'.ljust(player_width)}  "
            f"{'ELO'.rjust(elo_width)}  {'Adj'.rjust(adjusted_width)}  {'Fit'.ljust(fit_width)}"
        ),
        (
            f"{'-' * role_width}  {'-' * player_width}  "
            f"{'-' * elo_width}  {'-' * adjusted_width}  {'-' * fit_width}"
        ),
    ]
    for row in team.assignments:
        lines.append(
            f"{row.role.ljust(role_width)}  {row.player.name.ljust(player_width)}  "
            f"{str(row.player.elo).rjust(elo_width)}  {str(row.adjusted_elo).rjust(adjusted_width)}  {_fit_label(row.penalty).ljust(fit_width)}"
        )
    raw_avg = team.raw_total_elo / len(team.assignments)
    adjusted_avg = team.adjusted_total_elo / len(team.assignments)
    lines.append(f"Average ELO: {raw_avg:.1f} (role-adjusted: {adjusted_avg:.1f})")
    return "\n".join(lines)


def _format_draft_message(result: DraftResult) -> str:
    blue_avg = result.blue.adjusted_total_elo / len(result.blue.assignments)
    red_avg = result.red.adjusted_total_elo / len(result.red.assignments)
    diff = abs(blue_avg - red_avg)
    lines = [
        "```text",
        _format_team_table("Blue Team", result.blue),
        "",
        _format_team_table("Red Team", result.red),
        "",
        f"Adjusted average gap: {diff:.1f}",
        f"Handicap: secondary -{SECONDARY_ROLE_PENALTY}, off-role -{OFF_ROLE_PENALTY}",
        "```",
    ]
    return "\n".join(lines)


def _format_missing_setup_message(unknown_usernames: list[str], missing_roles: list[MappingRule]) -> str:
    lines = ["Can't draft yet: some available players are missing setup."]

    if unknown_usernames:
        lines.append("")
        lines.append("Unknown username -> name mappings:")
        for username in unknown_usernames:
            lines.append(
                f"- `{username}`: run `champsplayer add {username} <name> <primary_role> <secondary_role>`"
            )
        lines.append(
            "- If these are Discord names, add Discord linkage with "
            "`champsmatch linkdiscord <league_username> [@discord_user_or_id]`."
        )

    if missing_roles:
        lines.append("")
        lines.append("Players missing primary and/or secondary role:")
        for rule in missing_roles:
            primary = rule.primary_role or "<primary_role>"
            secondary = rule.secondary_role or "<secondary_role>"
            lines.append(
                f"- `{rule.username}` (`{rule.name}`): run "
                f"`champsplayer add {rule.username} {rule.name} {primary} {secondary}`"
            )

    lines.append("")
    lines.append("Template: `champsplayer add <league name (no tag)> <name> <primary_role> <secondary_role>`")
    return "\n".join(lines)


async def handle_draft(ctx, args, db_path: str) -> None:
    explicit, added, removed, wants_help = _parse_draft_args(args)
    if wants_help:
        await ctx.send(DRAFT_HELP)
        return

    resolver_state = _build_resolver_state(db_path)

    if explicit:
        base_tokens = list(explicit)
    else:
        base_tokens = _extract_voice_tokens(ctx, resolver_state.player_username_by_discord_id)

    merged_tokens: list[str] = []
    for token in [*base_tokens, *added]:
        cleaned = _clean_token(token)
        if not cleaned:
            continue
        if cleaned not in merged_tokens:
            merged_tokens.append(cleaned)

    added_players = _resolve_players(added, resolver_state)
    removed_players = _resolve_players(removed, resolver_state)
    added_name_keys = {row.name.casefold() for row in added_players}
    removed_name_keys = {row.name.casefold() for row in removed_players}
    overlap = sorted(added_name_keys & removed_name_keys)
    if overlap:
        overlap_names = ", ".join(resolver_state.canonical_name_by_casefold.get(name, name) for name in overlap)
        await ctx.send(f"Conflicting draft modifiers: player(s) included and excluded: {overlap_names}")
        return

    unknown_usernames: list[str] = []
    missing_roles_by_name: dict[str, MappingRule] = {}
    for token in merged_tokens:
        rule = _resolve_mapping_rule(token, resolver_state)
        if rule is None:
            unknown_usernames.append(token)
            continue
        if not rule.primary_role or not rule.secondary_role:
            missing_roles_by_name[rule.name.casefold()] = rule

    missing_roles = list(missing_roles_by_name.values())

    if unknown_usernames or missing_roles:
        await ctx.send(_format_missing_setup_message(unknown_usernames, missing_roles))
        return

    players = _resolve_players(merged_tokens, resolver_state)
    players = [player for player in players if player.name.casefold() not in removed_name_keys]

    required_players = len(ROLES) * 2
    if len(players) < required_players:
        source_hint = "voice channels (+/- overrides)" if not explicit else "explicit list (+/- overrides)"
        await ctx.send(
            f"Need exactly 10 unique players; resolved {len(players)} from {source_hint}.\n"
            "Use `champsdraft help` for syntax."
        )
        return
    sampled_from: int | None = None
    if len(players) > required_players:
        sampled_from = len(players)
        players = random.sample(players, required_players)

    try:
        result = _build_draft(players, randomize=True)
    except ValueError as exc:
        await ctx.send(str(exc))
        return
    if sampled_from is not None:
        await ctx.send(
            f"More than 10 players available ({sampled_from}). Randomly selected 10 for this draft.\n"
            f"{_format_draft_message(result)}"
        )
        return
    await ctx.send(_format_draft_message(result))
