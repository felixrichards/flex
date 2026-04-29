import asyncio
import itertools
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from champs.constants import (
    DODGE_MAX_NO_PENALTY,
    DODGE_PENALTY,
    DODGE_WINDOW_SECONDS,
    DRAFT_WINDOW_SECONDS,
    Privilege,
)
from champs.db import db
from champs.db.models import PlayerMappingRecord, PlayerRecord

ROLES: tuple[str, ...] = ("TOP", "JUNGLE", "MID", "BOT", "SUPP")
SECONDARY_ROLE_PENALTY = 20
OFF_ROLE_PENALTY = 40
RANDOM_GAP_SLACK = 10
METRIC_BUCKET_TARGET_DRAFTS = 24
METRIC_WEIGHT_DECAY = 0.5
ROLE_PRIORITY_MAX_GAP = 60
ROLE_PRIORITY_MIN_GAP = 10
ROLE_PRIORITY_GAP_STEP = 5

HELP = """`champsdraft` usage:

- `champsdraft`
  Use players currently in voice channels.

- `champsdraft <player_or_username> ...`
  Use an explicit player list (must resolve to 10 players).

- `champsdraft [<player_or_username> ...] [+player ...] [-player ...]`
  `+` opts a player in and `-` opts a player out.
  If no explicit list is provided, voice-channel players are used as the base.

Draft rules:
- One draft every 300 seconds.
- After a draft is posted, a 60 second dodge window opens.
- Submit dodges with `/dodge` (ephemeral)."""

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
    secondary_penalty_total: int
    off_role_penalty_total: int


@dataclass(frozen=True)
class DraftResult:
    blue: TeamDraft
    red: TeamDraft


@dataclass
class DraftWindowState:
    created_at: datetime
    active_players: list[DraftPlayer]
    player_pool: list[DraftPlayer]
    dodger_names: set[str]
    draft_history_signatures: set[tuple]
    window_end_task: asyncio.Task | None = None


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


DRAFT_STATE_BY_CHANNEL: dict[int, DraftWindowState] = {}


def _draft_signature(result: DraftResult) -> tuple:
    blue = tuple((row.role, row.player.name.casefold()) for row in result.blue.assignments)
    red = tuple((row.role, row.player.name.casefold()) for row in result.red.assignments)
    return (blue, red)


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
        canonical_name = state.latest_name_by_username.get(token_key)
    if canonical_name is None:
        return None

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


def _best_team_assignment(
    players: tuple[DraftPlayer, ...],
    *,
    randomize_ties: bool = False,
    rng: random.Random | None = None,
) -> TeamDraft:
    best: TeamDraft | None = None
    best_key = None
    tied_best: list[TeamDraft] = []
    for roles in itertools.permutations(ROLES, len(players)):
        assignments: list[TeamAssignment] = []
        raw_total = 0
        adjusted_total = 0
        total_penalty = 0
        secondary_penalty_total = 0
        off_role_penalty_total = 0
        for player, role in zip(players, roles):
            penalty = _role_penalty(player, role)
            adjusted = player.elo - penalty
            raw_total += player.elo
            adjusted_total += adjusted
            total_penalty += penalty
            if penalty == SECONDARY_ROLE_PENALTY:
                secondary_penalty_total += penalty
            elif penalty == OFF_ROLE_PENALTY:
                off_role_penalty_total += penalty
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
        )
        candidate = TeamDraft(
            assignments=ordered_assignments,
            raw_total_elo=raw_total,
            adjusted_total_elo=adjusted_total,
            total_penalty=total_penalty,
            secondary_penalty_total=secondary_penalty_total,
            off_role_penalty_total=off_role_penalty_total,
        )
        if best is None or key < best_key:
            best = candidate
            tied_best = [candidate]
            best_key = key
        elif key == best_key:
            tied_best.append(candidate)
    if best is None:
        raise ValueError("Could not assign team roles.")
    if randomize_ties and len(tied_best) > 1:
        rand = rng or random.Random()
        return rand.choice(tied_best)
    return best


def _build_draft(
    players: list[DraftPlayer],
    *,
    randomize: bool = False,
    rng: random.Random | None = None,
    forbidden_signatures: set[tuple] | None = None,
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
        drafted = _best_team_assignment(team_players, randomize_ties=randomize, rng=rng)
        assignment_cache[indices] = drafted
        return drafted

    forbidden = forbidden_signatures or set()
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
    non_forbidden = [(key, draft) for key, draft in candidate_results if _draft_signature(draft) not in forbidden]
    if not randomize:
        if non_forbidden:
            return non_forbidden[0][1]
        return candidate_results[0][1]

    rand = rng or random.Random()

    source = non_forbidden if non_forbidden else candidate_results
    by_metric: dict[int, list[tuple[tuple[int, int, tuple[str, ...], tuple[str, ...]], DraftResult]]] = {}
    for key, draft in source:
        metric = _role_metric_for_draft(draft)
        by_metric.setdefault(metric, []).append((key, draft))

    metrics = sorted(by_metric)
    selected_metrics: list[int] = []
    selected_count = 0
    for metric in metrics:
        selected_metrics.append(metric)
        selected_count += len(by_metric[metric])
        if selected_count >= METRIC_BUCKET_TARGET_DRAFTS:
            break

    if not selected_metrics:
        # Defensive fallback; should be unreachable because `source` is non-empty.
        return source[0][1]

    kept_entries: list[tuple[tuple[int, int, tuple[str, ...], tuple[str, ...]], DraftResult, int, int]] = []
    for rank, metric in enumerate(selected_metrics):
        allowed_gap = max(ROLE_PRIORITY_MIN_GAP, ROLE_PRIORITY_MAX_GAP - (metric * ROLE_PRIORITY_GAP_STEP))
        for key, draft in by_metric[metric]:
            adjusted_gap = key[0]
            if adjusted_gap <= allowed_gap:
                kept_entries.append((key, draft, rank, metric))

    if not kept_entries:
        for rank, metric in enumerate(selected_metrics):
            for key, draft in by_metric[metric]:
                kept_entries.append((key, draft, rank, metric))

    weighted_drafts: list[DraftResult] = []
    weights: list[float] = []
    for _, draft, rank, _ in kept_entries:
        weighted_drafts.append(draft)
        weights.append(METRIC_WEIGHT_DECAY**rank)

    return rand.choices(weighted_drafts, weights=weights, k=1)[0]


def _role_metric_for_draft(result: DraftResult) -> int:
    # Role-priority metric: +1 per secondary assignment, +2 per off-role assignment.
    secondary_count = (result.blue.secondary_penalty_total + result.red.secondary_penalty_total) // SECONDARY_ROLE_PENALTY
    off_role_count = (result.blue.off_role_penalty_total + result.red.off_role_penalty_total) // OFF_ROLE_PENALTY
    return int(secondary_count + (2 * off_role_count))


def _fit_label(penalty: int) -> str:
    if penalty == 0:
        return "Primary"
    if penalty == SECONDARY_ROLE_PENALTY:
        return "Secondary"
    return "Off-role"


def _format_team_table(name: str, team: TeamDraft) -> str:
    role_width = max(len("Role"), *(len(row.role) for row in team.assignments))
    player_width = max(len("Player"), *(len(row.player.name) for row in team.assignments))
    fit_width = max(len("Fit"), *(len(_fit_label(row.penalty)) for row in team.assignments))

    lines = [
        name,
        f"{'Role'.ljust(role_width)}  {'Player'.ljust(player_width)}  {'Fit'.ljust(fit_width)}",
        f"{'-' * role_width}  {'-' * player_width}  {'-' * fit_width}",
    ]
    for row in team.assignments:
        lines.append(
            f"{row.role.ljust(role_width)}  {row.player.name.ljust(player_width)}  {_fit_label(row.penalty).ljust(fit_width)}"
        )
    raw_avg = team.raw_total_elo / len(team.assignments)
    adjusted_avg = team.adjusted_total_elo / len(team.assignments)
    lines.append(f"Average ELO: {raw_avg:.1f} (role-adjusted: {adjusted_avg:.1f})")
    return "\n".join(lines)


def _format_draft_message(result: DraftResult) -> str:
    blue_avg = result.blue.adjusted_total_elo / len(result.blue.assignments)
    red_avg = result.red.adjusted_total_elo / len(result.red.assignments)
    diff = abs(blue_avg - red_avg)
    role_metric = _role_metric_for_draft(result)
    adjusted_gap = abs(result.blue.adjusted_total_elo - result.red.adjusted_total_elo)
    lines = [
        "```text",
        _format_team_table("Blue Team", result.blue),
        "",
        _format_team_table("Red Team", result.red),
        "",
        f"Adjusted average gap: {diff:.1f}",
        f"Debug: role metric={role_metric}, adjusted gap={adjusted_gap}",
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
            "`champsplayer linkdiscord <player_or_username> [@discord_user_or_id]`."
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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_seconds(seconds: int) -> str:
    safe = max(0, int(seconds))
    mins, secs = divmod(safe, 60)
    return f"{mins:02d}:{secs:02d}"


def _select_redraft_players(
    *,
    active_players: list[DraftPlayer],
    player_pool: list[DraftPlayer],
    dodger_names: set[str],
    rng: random.Random | None = None,
) -> list[DraftPlayer]:
    dodger_name_keys = {name.casefold() for name in dodger_names}
    guaranteed = [player for player in active_players if player.name.casefold() not in dodger_name_keys]
    guaranteed_keys = {player.name.casefold() for player in guaranteed}

    required_players = len(ROLES) * 2
    remaining = required_players - len(guaranteed)
    if remaining <= 0:
        return guaranteed[:required_players]

    candidates: list[DraftPlayer] = []
    seen_candidate_keys: set[str] = set()
    for player in player_pool:
        key = player.name.casefold()
        if key in guaranteed_keys or key in seen_candidate_keys:
            continue
        candidates.append(player)
        seen_candidate_keys.add(key)

    if len(candidates) < remaining:
        raise ValueError("Could not build redraft: insufficient replacement candidates.")

    rand = rng or random.Random()
    if len(candidates) == remaining:
        picked = list(candidates)
    else:
        picked = rand.sample(candidates, remaining)

    # Force a fresh lobby composition whenever alternatives exist.
    # If there are bench players, prefer that at least one replacement is from bench.
    active_key_set = {player.name.casefold() for player in active_players}
    bench_candidates = [player for player in candidates if player.name.casefold() not in active_key_set]
    picked_keys = {player.name.casefold() for player in picked}
    if bench_candidates and not any(player.name.casefold() in picked_keys for player in bench_candidates):
        chosen_bench = rand.choice(bench_candidates)
        picked[0] = chosen_bench

    return [*guaranteed, *picked]


def _resolve_draft_players(
    ctx,
    args,
    db_path: str,
) -> tuple[list[DraftPlayer] | None, list[DraftPlayer] | None, str | None]:
    explicit, added, removed, wants_help = _parse_draft_args(args)
    if wants_help:
        return None, None, HELP

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
        return None, None, f"Conflicting draft modifiers: player(s) included and excluded: {overlap_names}"

    unknown_usernames: list[str] = []
    missing_roles_by_name: dict[str, MappingRule] = {}
    for token in merged_tokens:
        player = _resolve_player_identifier(token, resolver_state)
        if player is None:
            unknown_usernames.append(token)
            continue
        if not player.primary_role or not player.secondary_role:
            rule = _resolve_mapping_rule(token, resolver_state) or MappingRule(
                username=token,
                name=player.name,
                primary_role=player.primary_role,
                secondary_role=player.secondary_role,
            )
            missing_roles_by_name[player.name.casefold()] = rule

    missing_roles = list(missing_roles_by_name.values())

    if unknown_usernames or missing_roles:
        return None, None, _format_missing_setup_message(unknown_usernames, missing_roles)

    players = _resolve_players(merged_tokens, resolver_state)
    players = [player for player in players if player.name.casefold() not in removed_name_keys]

    required_players = len(ROLES) * 2
    if len(players) < required_players:
        source_hint = "voice channels (+/- overrides)" if not explicit else "explicit list (+/- overrides)"
        return None, None, (
            f"Need exactly 10 unique players; resolved {len(players)} from {source_hint}.\n"
            "Use `champsdraft help` for syntax."
        )
    player_pool = list(players)
    sampled_from: int | None = None
    if len(players) > required_players:
        sampled_from = len(players)
        players = random.sample(players, required_players)

    warning = None
    if sampled_from is not None:
        warning = f"More than 10 players available ({sampled_from}). Randomly selected 10 for this draft."
    return players, player_pool, warning


async def _finalize_dodge_window(channel_id: int, ctx, db_path: str) -> None:
    state = DRAFT_STATE_BY_CHANNEL.get(channel_id)
    if state is None:
        return
    if state.window_end_task is not None and state.window_end_task.cancelled():
        return

    dodger_names = sorted(state.dodger_names, key=str.casefold)
    if not dodger_names:
        state.window_end_task = None
        await ctx.send("Dodge window closed. Draft locked.")
        return

    if len(dodger_names) > DODGE_MAX_NO_PENALTY:
        state.window_end_task = None
        next_players = _select_redraft_players(
            active_players=state.active_players,
            player_pool=state.player_pool,
            dodger_names=state.dodger_names,
        )
        await ctx.send(
            f"Dodge window closed: {len(dodger_names)} dodges. No CP penalty applied (threshold: >{DODGE_MAX_NO_PENALTY}). "
            "Posting a new draft."
        )
        await _post_new_draft(
            ctx,
            db_path,
            players=next_players,
            player_pool=state.player_pool,
            previous_signatures=state.draft_history_signatures,
        )
        return

    base_penalty = DODGE_PENALTY / float(len(dodger_names))
    applied_parts: list[str] = []
    for name in dodger_names:
        penalty = db.apply_dodge_penalty(
            db_path,
            name,
            base_penalty,
            source="draft_dodge",
            channel_id=channel_id,
        )
        applied_parts.append(f"{name} -{penalty} CP")

    state.window_end_task = None
    next_players = _select_redraft_players(
        active_players=state.active_players,
        player_pool=state.player_pool,
        dodger_names=state.dodger_names,
    )
    await ctx.send(
        "Dodge window closed. Penalties applied: "
        + ", ".join(applied_parts)
        + ". Posting a new draft."
    )
    await _post_new_draft(
        ctx,
        db_path,
        players=next_players,
        player_pool=state.player_pool,
        previous_signatures=state.draft_history_signatures,
    )


async def _open_dodge_window(
    channel_id: int,
    ctx,
    db_path: str,
    *,
    active_players: list[DraftPlayer],
    player_pool: list[DraftPlayer],
    draft_history_signatures: set[tuple],
) -> None:
    state = DraftWindowState(
        created_at=_utc_now(),
        active_players=list(active_players),
        player_pool=list(player_pool),
        dodger_names=set(),
        draft_history_signatures=set(draft_history_signatures),
        window_end_task=None,
    )
    DRAFT_STATE_BY_CHANNEL[channel_id] = state

    async def _runner() -> None:
        await asyncio.sleep(DODGE_WINDOW_SECONDS)
        await _finalize_dodge_window(channel_id, ctx, db_path)

    state.window_end_task = asyncio.create_task(_runner())


def _clear_channel_draft_state(channel_id: int) -> None:
    state = DRAFT_STATE_BY_CHANNEL.get(channel_id)
    if state is None:
        return
    if state.window_end_task is not None and not state.window_end_task.done():
        state.window_end_task.cancel()
    DRAFT_STATE_BY_CHANNEL.pop(channel_id, None)


async def _post_new_draft(
    ctx,
    db_path: str,
    *,
    players: list[DraftPlayer],
    player_pool: list[DraftPlayer],
    previous_signatures: set[tuple] | None = None,
    prefix_message: str | None = None,
) -> None:
    channel_id = getattr(getattr(ctx, "channel", None), "id", 0)
    seen_signatures = set(previous_signatures or set())
    try:
        result = _build_draft(players, randomize=True, forbidden_signatures=seen_signatures)
    except ValueError as exc:
        await ctx.send(str(exc))
        return
    seen_signatures.add(_draft_signature(result))
    message = _format_draft_message(result) + "\n" + f"Dodge window: `{DODGE_WINDOW_SECONDS}s`. Use `/dodge` to dodge: 10 CP penalty shared between all dodgers."
    if prefix_message:
        message = prefix_message + "\n" + message
    await ctx.send(message)
    await _open_dodge_window(
        channel_id,
        ctx,
        db_path,
        active_players=players,
        player_pool=player_pool,
        draft_history_signatures=seen_signatures,
    )


async def handle_draft(ctx, args, db_path: str) -> None:
    channel_id = getattr(getattr(ctx, "channel", None), "id", 0)

    now = _utc_now()
    state = DRAFT_STATE_BY_CHANNEL.get(channel_id)
    if state is not None:
        elapsed = now - state.created_at
        if elapsed < timedelta(seconds=DRAFT_WINDOW_SECONDS):
            caller_privilege = db.get_discord_user_privilege(db_path, ctx.author.id)
            if caller_privilege < int(Privilege.ADMIN):
                remaining = int((timedelta(seconds=DRAFT_WINDOW_SECONDS) - elapsed).total_seconds())
                await ctx.send(
                    "Draft cooldown active in this channel. "
                    f"Please wait `{_format_seconds(remaining)}` before requesting another draft."
                )
                return
            _clear_channel_draft_state(channel_id)

    players, player_pool, result_message = _resolve_draft_players(ctx, args, db_path)
    if players is None:
        await ctx.send(result_message or HELP)
        return
    assert player_pool is not None
    await _post_new_draft(
        ctx,
        db_path,
        players=players,
        player_pool=player_pool,
        prefix_message=result_message,
    )


async def handle_dodge(ctx, db_path: str) -> str:
    channel_id = getattr(getattr(ctx, "channel", None), "id", 0)

    state = DRAFT_STATE_BY_CHANNEL.get(channel_id)
    if state is None:
        return "No active draft in this channel."

    elapsed = _utc_now() - state.created_at
    if elapsed >= timedelta(seconds=DODGE_WINDOW_SECONDS):
        return "Dodge window is already closed for this draft."

    caller_name = db.get_discord_linked_player_name(db_path, ctx.author.id)
    if caller_name is None:
        return "Your Discord account is not linked to a player. Use `champsplayer linkdiscord` first."

    draft_name_keys = {player.name.casefold() for player in state.active_players}
    if caller_name.casefold() not in draft_name_keys:
        return "You are not part of the current draft lobby."

    if caller_name in state.dodger_names:
        return "Dodge already submitted for this draft."

    state.dodger_names.add(caller_name)
    remaining = int((timedelta(seconds=DODGE_WINDOW_SECONDS) - elapsed).total_seconds())
    return f"Dodge submitted for `{caller_name}`. Window closes in `{_format_seconds(remaining)}`."
