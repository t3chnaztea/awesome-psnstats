"""All psnawp / PSN API access lives here.

The transform from a psnawp ``TitleStats`` to our :class:`~psnstats.analysis.Game`
is a pure function (:func:`normalize_title_stat`) so it can be tested with
lightweight stand-ins and zero network. Everything that actually talks to Sony is
a thin wrapper that raises our own error types.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import timezone

from psnawp_api import PSNAWP
from psnawp_api.core.psnawp_exceptions import (
    PSNAWPAuthenticationError,
    PSNAWPForbiddenError,
    PSNAWPInvalidTokenError,
    PSNAWPNotFoundError,
    PSNAWPUnauthorizedError,
)
from psnawp_api.models.title_stats import PlatformCategory

from .analysis import Game

# psnawp only ever reports these two categories with playtime; everything else
# (the enum's UNKNOWN, and PS3/Vita which carry no playtime in Sony's API) is
# bucketed as OTHER.
PLATFORM_LABEL = {PlatformCategory.PS4: "PS4", PlatformCategory.PS5: "PS5"}

# psnawp self-rate-limits to 300 req / 15 min; keep trophy batches small.
TROPHY_BATCH_SIZE = 5

# The store wishlist has no documented endpoint; this is the persisted GraphQL
# query the PS App itself uses (community-documented in
# andshrew/PlayStation-Trophies). Sony can rotate the hash without notice, in
# which case fetch_wishlist raises WishlistUnavailableError.
WISHLIST_URL = "https://m.np.playstation.com/api/graphql/v1/op"
WISHLIST_OPERATION = "metGetStoreWishlist"
WISHLIST_QUERY_HASH = "571149e8aa4d76af7dd33b92e1d6f8f828ebc5fa8f0f6bf51a8324a0e6d71324"


class AuthError(Exception):
    """NPSSO missing, malformed, or expired."""


class UserNotFoundError(Exception):
    """Requested --user online_id does not exist."""


class ForbiddenError(Exception):
    """Target library/trophies are private."""


class WishlistUnavailableError(Exception):
    """The wishlist GraphQL query was rejected or returned an unexpected shape
    (most likely Sony rotated the persisted-query hash)."""


def platform_label(category) -> str:
    return PLATFORM_LABEL.get(category, "OTHER")


def normalize_title_stat(stat) -> Game:
    """Pure: convert a psnawp ``TitleStats`` into a :class:`Game`.

    Playtime is kept as a float (hours) and ``last_played`` as the full
    timestamp; rounding/truncation happens only at render time.
    """
    duration = getattr(stat, "play_duration", None)
    playtime_hours = duration.total_seconds() / 3600.0 if duration else 0.0
    # psnawp hands back timezone-aware timestamps; normalize to naive UTC so the
    # rest of the pipeline (and the analysis clock) can compare them freely.
    last_played = getattr(stat, "last_played_date_time", None)
    if last_played is not None and last_played.tzinfo is not None:
        last_played = last_played.astimezone(timezone.utc).replace(tzinfo=None)
    return Game(
        title=stat.name or "Unknown",
        title_id=getattr(stat, "title_id", "") or "",
        system=platform_label(getattr(stat, "category", None)),
        playtime_hours=playtime_hours,
        play_count=getattr(stat, "play_count", 0) or 0,
        last_played=last_played,
        completion_progress=None,
    )


def authenticate(npsso: str):
    """Return ``(psnawp, client, online_id)``. Raises :class:`AuthError`."""
    try:
        psnawp = PSNAWP(npsso)
        client = psnawp.me()
        online_id = client.online_id
    except (
        PSNAWPAuthenticationError,
        PSNAWPInvalidTokenError,
        PSNAWPUnauthorizedError,
    ) as exc:
        raise AuthError(str(exc)) from exc
    return psnawp, client, online_id


def resolve_source(psnawp, client, online_id: str | None):
    """Return ``(source, display_name)`` for stats + trophy calls.

    ``source`` is the authenticated client (own library) or a resolved public
    ``User``. Raises :class:`UserNotFoundError` for a bad ``--user``.
    """
    if online_id:
        try:
            user = psnawp.user(online_id=online_id)
        except (PSNAWPNotFoundError, PSNAWPForbiddenError) as exc:
            raise UserNotFoundError(online_id) from exc
        return user, online_id
    return client, client.online_id


def fetch_title_stats(
    source,
    platforms: Iterable[str],
    min_hours: float,
    limit: int | None = None,
    on_game: Callable[[Game], None] | None = None,
) -> tuple[list[Game], dict]:
    """Page through the library, filter, and normalize.

    Returns ``(games_sorted_by_playtime_desc, fetch_stats)``. ``on_game`` is an
    optional progress callback invoked for each kept game.
    """
    wanted = {p.lower() for p in platforms}
    games: list[Game] = []
    total = 0
    skipped_platform = 0
    skipped_playtime = 0

    try:
        for stat in source.title_stats(page_size=100):
            total += 1
            game = normalize_title_stat(stat)
            if game.system.lower() not in wanted:
                skipped_platform += 1
                continue
            if game.playtime_hours < min_hours:
                skipped_playtime += 1
                continue
            games.append(game)
            if on_game is not None:
                on_game(game)
            if limit and len(games) >= limit:
                break
    except PSNAWPForbiddenError as exc:
        raise ForbiddenError(str(exc)) from exc

    games.sort(key=lambda g: g.playtime_hours, reverse=True)
    fetch_stats = {
        "total_fetched": total,
        "skipped_platform": skipped_platform,
        "skipped_playtime": skipped_playtime,
        "included": len(games),
    }
    return games, fetch_stats


@dataclass
class WishlistItem:
    """One store-wishlist entry.

    ``kind`` is Sony's ``__typename``: ``Product`` (a purchasable SKU, possibly
    one of several editions) or ``Concept`` (an unreleased game with no SKU yet,
    e.g. a pre-announcement page). Concepts have no platforms/classification/price.
    Prices are Sony's localized display strings (e.g. ``"$19.99"``), kept verbatim.
    """

    name: str
    product_id: str
    kind: str
    platforms: list[str] = field(default_factory=list)
    classification: str = ""
    base_price: str = ""
    discounted_price: str = ""
    discount_text: str = ""
    box_art_url: str = ""


def normalize_wishlist_entry(entry: dict) -> WishlistItem:
    """Pure: convert one raw ``storeWishlist`` element into a :class:`WishlistItem`."""
    box_art = entry.get("boxArt") or {}
    price = entry.get("price") or {}
    return WishlistItem(
        name=entry.get("name") or "Unknown",
        product_id=str(entry.get("id") or ""),
        kind=entry.get("__typename") or "Product",
        platforms=[p for p in (entry.get("platforms") or []) if p],
        classification=entry.get("storeDisplayClassification") or "",
        base_price=price.get("basePrice") or "",
        discounted_price=price.get("discountedPrice") or "",
        discount_text=price.get("discountText") or "",
        box_art_url=box_art.get("url") or "",
    )


def fetch_wishlist(psnawp) -> list[WishlistItem]:
    """Fetch the authenticated account's store wishlist.

    Own-account only: Sony exposes no public wishlist for other users.
    Raises :class:`WishlistUnavailableError` if the persisted query is rejected
    or the response shape changed.
    """
    params = {
        "operationName": WISHLIST_OPERATION,
        "variables": "{}",
        "extensions": json.dumps(
            {"persistedQuery": {"version": 1, "sha256Hash": WISHLIST_QUERY_HASH}},
            separators=(",", ":"),
        ),
    }
    # Apollo's CSRF guard rejects the request without an operation-name (or
    # JSON content-type) header; these are the headers the PS App sends.
    headers = {
        "x-apollo-operation-name": WISHLIST_OPERATION,
        "content-type": "application/json",
    }
    try:
        payload = psnawp.authenticator.get(
            url=WISHLIST_URL, params=params, headers=headers
        ).json()
    except PSNAWPForbiddenError as exc:
        raise ForbiddenError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - any 4xx/5xx/parse error means "unavailable"
        raise WishlistUnavailableError(str(exc)) from exc

    entries = (payload.get("data") or {}).get("storeWishlist")
    if entries is None:
        detail = payload.get("errors") or "no storeWishlist key in response"
        raise WishlistUnavailableError(
            f"unexpected response (Sony may have rotated the query hash): {detail}"
        )
    return [normalize_wishlist_entry(e) for e in entries]


def enrich_trophies(
    source,
    games: list[Game],
    on_progress: Callable[[int, int], None] | None = None,
    batch_size: int = TROPHY_BATCH_SIZE,
) -> int:
    """Fill ``completion_progress`` from trophy data. Returns count enriched.

    Best-effort: a failed batch (rate limit, private set) is skipped rather than
    aborting the whole run. Matches trophy rows back to games by ``np_title_id``.
    """
    by_id = {g.title_id: g for g in games if g.title_id}
    ids = list(by_id)
    enriched = 0
    for i in range(0, len(ids), batch_size):
        batch = ids[i : i + batch_size]
        try:
            for tt in source.trophy_titles_for_title(batch):
                np_id = getattr(tt, "np_title_id", None)
                progress = getattr(tt, "progress", None)
                game = by_id.get(np_id)
                if game is not None and progress is not None:
                    game.completion_progress = float(progress)
                    enriched += 1
        except (PSNAWPForbiddenError, PSNAWPNotFoundError, PSNAWPAuthenticationError):
            continue
        if on_progress is not None:
            on_progress(min(i + batch_size, len(ids)), len(ids))
    return enriched
